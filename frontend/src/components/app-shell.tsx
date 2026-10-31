"use client";

import { Ghost, History, LayoutDashboard, ScanSearch, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { RuntimeBadge } from "@/components/runtime-status";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/investigations/new", label: "New investigation", icon: ScanSearch },
  { href: "/investigations", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2 rounded-md font-semibold tracking-tight">
      <span className="ghost-glow flex size-8 items-center justify-center rounded-lg border border-primary/30 bg-primary/10">
        <Ghost className="size-4.5 text-primary" aria-hidden />
      </span>
      GhostRepo
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const links = NAV.map(({ href, label, icon: Icon }) => {
    const active = pathname === href;
    return (
      <Link
        key={href}
        href={href}
        aria-current={active ? "page" : undefined}
        className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors ${
          active
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground"
        }`}
      >
        <Icon className="size-4 shrink-0" aria-hidden />
        {label}
      </Link>
    );
  });

  return (
    <div className="ghost-backdrop flex min-h-screen flex-col md:flex-row">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar/80 p-4 md:sticky md:top-0 md:flex md:h-screen">
        <Brand />
        <nav aria-label="Main" className="mt-8 flex flex-col gap-1">
          {links}
        </nav>
        <div className="mt-auto border-t border-sidebar-border pt-4">
          <RuntimeBadge />
        </div>
      </aside>

      <header className="flex flex-col gap-3 border-b border-sidebar-border bg-sidebar/80 p-4 md:hidden">
        <div className="flex items-center justify-between gap-3">
          <Brand />
          <RuntimeBadge />
        </div>
        <nav aria-label="Main" className="-mx-1 flex gap-1 overflow-x-auto px-1">
          {links}
        </nav>
      </header>

      <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
