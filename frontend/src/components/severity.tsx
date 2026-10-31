import { CircleAlert, Info, OctagonAlert, TriangleAlert, type LucideIcon } from "lucide-react";

import type { Severity } from "@/lib/types";

export const SEVERITY_STYLE: Record<
  Severity,
  { label: string; icon: LucideIcon; text: string; bar: string; border: string }
> = {
  critical: {
    label: "Critical",
    icon: OctagonAlert,
    text: "text-severity-critical",
    bar: "bg-severity-critical",
    border: "border-severity-critical/40",
  },
  high: {
    label: "High",
    icon: TriangleAlert,
    text: "text-severity-high",
    bar: "bg-severity-high",
    border: "border-severity-high/40",
  },
  medium: {
    label: "Medium",
    icon: TriangleAlert,
    text: "text-severity-medium",
    bar: "bg-severity-medium",
    border: "border-severity-medium/40",
  },
  low: {
    label: "Low",
    icon: CircleAlert,
    text: "text-severity-low",
    bar: "bg-severity-low",
    border: "border-severity-low/40",
  },
  info: {
    label: "Informational",
    icon: Info,
    text: "text-severity-info",
    bar: "bg-severity-info",
    border: "border-severity-info/40",
  },
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  const style = SEVERITY_STYLE[severity];
  const Icon = style.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${style.border}`}
    >
      <Icon className={`size-3 ${style.text}`} aria-hidden />
      {style.label}
    </span>
  );
}
