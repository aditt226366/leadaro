"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Megaphone, Users, Radio, AudioLines, FileText,
  BarChart3, Workflow, Plug, Settings, ShieldCheck, PhoneCall, Bot, PhoneIncoming,
  PanelLeftClose, Rocket, Menu,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { Chip } from "@/components/ui/Chip";

export type Mode = "voice" | "call";

type Item = {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  badge?: string;
  /** Omit for both modes; set to restrict. */
  only?: Mode;
};

const SECTIONS: { label: string; items: Item[] }[] = [
  {
    label: "General",
    items: [
      { href: "", label: "Dashboard", icon: LayoutDashboard },
      { href: "/campaigns", label: "Campaigns", icon: Megaphone },
      { href: "/leads", label: "Leads", icon: Users },
      { href: "/monitor", label: "Live Monitor", icon: Radio },
      { href: "/calls", label: "Call History", icon: PhoneCall },
      { href: "/ivr", label: "Inbound & IVR", icon: PhoneIncoming },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/voices", label: "Voice Library", icon: AudioLines },
      { href: "/scripts", label: "Scripts", icon: FileText },
      { href: "/agents", label: "Agent Workspace", icon: Bot, only: "call" },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
      { href: "/automation", label: "Automation", icon: Workflow, badge: "BETA" },
    ],
  },
  {
    label: "Support",
    items: [
      { href: "/integrations", label: "Integrations", icon: Plug },
      { href: "/compliance", label: "Compliance", icon: ShieldCheck },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

export function Sidebar({ mode }: { mode: Mode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  // Close the drawer on navigation — otherwise it stays over the page you just
  // opened on a phone.
  useEffect(() => setOpen(false), [pathname]);

  const base = `/${mode}`;
  const isActive = (href: string) => {
    const full = `${base}${href}`;
    return href === "" ? pathname === full : pathname.startsWith(full);
  };

  const switchMode = (next: Mode) => {
    // Keep the user on the same sub-page when switching surfaces.
    const rest = pathname.replace(/^\/(voice|call)/, "");
    document.cookie = `mode=${next};path=/;max-age=31536000;samesite=lax`;
    router.push(`/${next}${rest}`);
  };

  return (
    <>
      {/* Mobile trigger — the sidebar is a drawer below lg. */}
      <button
        onClick={() => setOpen(true)}
        aria-label="Open navigation"
        className="fixed left-3 top-3 z-40 grid size-9 place-items-center rounded-pill border border-line-strong bg-surface text-ink shadow-card lg:hidden"
      >
        <Menu size={16} />
      </button>

      {open && (
        <div
          onClick={() => setOpen(false)}
          className="fixed inset-0 z-30 bg-ink/25 lg:hidden"
          aria-hidden
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-sidebar flex-col border-r border-line bg-surface",
          "transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
      {/* brand */}
      <div className="flex h-14 items-center justify-between px-4">
        <Link href={`${base}`} className="flex items-center gap-2">
          <span className="grid size-6 place-items-center rounded-md bg-gradient-to-br from-primary-deep to-c5">
            <AudioLines size={13} strokeWidth={2.5} className="text-white" />
          </span>
          <span className="text-md font-semibold tracking-tight text-ink">Leadaro</span>
        </Link>
        <button
          onClick={() => setOpen(false)}
          className="text-faint hover:text-muted"
          aria-label="Close navigation"
        >
          <PanelLeftClose size={15} />
        </button>
      </div>

      {/* mode switcher — the Voice ⇄ Call surface toggle */}
      <div className="px-3 pb-3">
        <div
          role="tablist"
          aria-label="Outreach surface"
          className="grid grid-cols-2 gap-0.5 rounded-pill bg-sunk p-0.5"
        >
          {(["voice", "call"] as Mode[]).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              onClick={() => switchMode(m)}
              className={cn(
                "rounded-[6px] py-1.5 text-tiny font-semibold capitalize transition-colors",
                mode === m
                  ? "bg-surface text-primary-ink shadow-card"
                  : "text-muted hover:text-ink",
              )}
            >
              {m === "voice" ? "Voice" : "Call"}
            </button>
          ))}
        </div>
      </div>

      {/* nav */}
      <nav className="flex-1 overflow-y-auto px-3 pb-4">
        {SECTIONS.map((section) => {
          const items = section.items.filter((i) => !i.only || i.only === mode);
          if (!items.length) return null;
          return (
            <div key={section.label} className="mb-5">
              <p className="mb-1.5 px-2 text-micro font-semibold uppercase text-faint">
                {section.label}
              </p>
              <ul className="space-y-0.5">
                {items.map((item) => {
                  const active = isActive(item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={`${base}${item.href}`}
                        className={cn(
                          "flex items-center gap-2.5 rounded-pill px-2 py-1.5 text-base transition-colors",
                          active
                            ? "bg-primary-wash font-semibold text-primary-ink"
                            : "font-medium text-muted hover:bg-sunk hover:text-ink",
                        )}
                      >
                        <item.icon size={15} strokeWidth={active ? 2.3 : 2} />
                        <span className="flex-1 truncate">{item.label}</span>
                        {item.badge && (
                          <Chip tone="primary" className="px-1 py-0 text-[9px]">
                            {item.badge}
                          </Chip>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      {/* footer */}
      <div className="border-t border-line p-3">
        <div className="rounded-card bg-gradient-to-br from-primary-deep to-[#7C5CE7] p-3 text-white">
          <div className="flex items-center gap-1.5">
            <Rocket size={13} />
            <p className="text-sm font-semibold">Boost your outreach</p>
          </div>
          <p className="mt-1 text-tiny/4 text-white/80">
            Unlock unlimited AI voice minutes and custom voice cloning.
          </p>
          <button className="mt-2.5 w-full rounded-md bg-white/95 py-1.5 text-tiny font-semibold text-primary-deep hover:bg-white">
            Upgrade Plan
          </button>
        </div>
        <p className="mt-3 px-1 text-[10px] text-faint">© 2026 Leadaro, Inc.</p>
      </div>
      </aside>
    </>
  );
}
