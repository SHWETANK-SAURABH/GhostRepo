"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, RotateCcw } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { toast } from "sonner";

import { ConfirmButton } from "@/components/confirm-button";
import { isActive, useReport } from "@/components/investigation/use-report";
import { ErrorState } from "@/components/states";
import { StatusBadge } from "@/components/status-badge";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api";
import type { Report } from "@/lib/types";

const PROVENANCE: Record<Report["provenance"], string> = {
  deterministic: "Deterministic analyzers only",
  deterministic_and_ai: "Deterministic analyzers and local AI",
  none: "No results yet",
};

export function InvestigationFrame({ id, children }: { id: string; children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data, isPending, isError, error, refetch } = useReport(id);

  const rerun = useMutation({
    mutationFn: (path: string) => api.startInvestigation(path),
    onSuccess: (next) => {
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      router.push(`/investigations/${next.id}`);
    },
    onError: (failure) => toast.error(errorMessage(failure)),
  });

  if (isPending) return <Skeleton className="h-40 rounded-xl" />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;

  const investigation = data.investigation;
  const root = `/investigations/${id}`;
  const tabs = [
    { href: root, label: "Autopsy" },
    { href: `${root}/findings`, label: "Findings" },
    { href: `${root}/plan`, label: "Resurrection plan" },
    { href: `${root}/readme`, label: "README" },
    { href: `${root}/patches`, label: "Patches" },
  ];
  const relativePath = investigation.repository.relative_path;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <h1 className="truncate font-mono text-2xl font-semibold tracking-tight">
            {investigation.repository.name}
          </h1>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <StatusBadge status={investigation.status} />
            <span>{new Date(investigation.created_at).toLocaleString()}</span>
            <span>Results from: {PROVENANCE[data.provenance]}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={api.exportUrl(id, "markdown")}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            <Download aria-hidden />
            Markdown
          </a>
          <a
            href={api.exportUrl(id, "json")}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            <Download aria-hidden />
            JSON
          </a>
          {relativePath && !isActive(investigation) && (
            <ConfirmButton
              variant="outline"
              size="sm"
              disabled={rerun.isPending}
              title="Investigate this repository again?"
              description="This scans the current state of the repository and creates a new report. This report is kept."
              confirmLabel="Investigate again"
              onConfirm={() => rerun.mutate(relativePath)}
            >
              <RotateCcw aria-hidden />
              Investigate again
            </ConfirmButton>
          )}
        </div>
      </div>

      <nav aria-label="Report sections" className="-mx-1 overflow-x-auto px-1">
        <ul className="flex min-w-max gap-1 border-b border-border">
          {tabs.map((tab) => {
            const active = pathname === tab.href;
            return (
              <li key={tab.href}>
                <Link
                  href={tab.href}
                  aria-current={active ? "page" : undefined}
                  className={`block border-b-2 px-3 py-2 text-sm transition-colors ${
                    active
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {children}
    </div>
  );
}
