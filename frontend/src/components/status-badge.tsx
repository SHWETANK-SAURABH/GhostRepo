import { CircleCheck, CircleDashed, CircleX, Clock, LoaderCircle, Unplug } from "lucide-react";

const STATUS = {
  queued: { label: "Queued", icon: Clock, color: "text-muted-foreground" },
  running: { label: "Running", icon: LoaderCircle, color: "text-primary animate-spin" },
  completed: { label: "Completed", icon: CircleCheck, color: "text-primary" },
  failed: { label: "Failed", icon: CircleX, color: "text-destructive" },
  interrupted: { label: "Interrupted", icon: Unplug, color: "text-severity-high" },
} as const;

export function StatusBadge({ status }: { status: string }) {
  const known = STATUS[status as keyof typeof STATUS];
  const Icon = known?.icon ?? CircleDashed;
  return (
    <span className="inline-flex items-center gap-1 text-xs whitespace-nowrap">
      <Icon className={`size-3.5 ${known?.color ?? "text-muted-foreground"}`} aria-hidden />
      {known?.label ?? status}
    </span>
  );
}
